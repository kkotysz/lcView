c
c  dopasowuje iteracyjnie n sinusoid (+ harmoniki + czestosci kombincyjne)
c  do danych obserwacyjnych postaci:
c  czas,mag,blad
c
      program sinnite
      implicit double precision (a-h,o-z)
      character *2 c
      character *11 nameb
      character *5 ccol
      character *50 ccc
      external nonlin
      parameter (NP = 1000000,NPAR = 1500, NHAR = 500, NPER = 500)
      dimension y(NP),ti(NP),x(NPAR),eps(NPAR),per(NPER),
     *     fi(NPER),freq(NPER),om(NPER),waga(NP),covar(NPAR,NPAR),
     *     ia(NPAR),amp(NPER),res(NP),freqb(NPER),nharm(NHAR,NPER),
     *     idx(NPER),tmax(NPER),err(NP),amass(NP)
      common /fff/ freq,fi,amp,freqb,nharm
      data pi2 /6.2831853072d0/
      data fact /0.7d0/

      narg = command_argument_count()
      if (narg.ne.1) then
         write (*,'(/'' Wrong number of arguments'')')
         write (*,'('' Usage: hars-ite <cstop>'')')
         stop
      end if
      write (*,'(/'' --- hars-ite, ver. 2.0, 22 Oct 2014 ---'')')
      write (*,'('' Defaults names:'')')
      write (*,'(''  I - data file: lc.data'')')
      write (*,'(''  I - freq: frequency file'')')
      write (*,'(''  I - param.sin: parameters from hars-sin'')')
      write (*,'(''  O - residuals: resid.dat'')')
      write (*,'(''  O - ampl: parameters'')')

      call get_command_argument(1,ccc)
      read (ccc,*) cstop

   87 continue

c
c
c
      open (3,file = 'param.sin')
      read (3,*) mfreq,m
c
c  mfreq - number of basic frequencies
c  m - number of sinusoidal terms
c  mm - number of unknowns
c
c     mm - liczba parametrow dopasowywanych:
c       liczba czestosci (dla kazdej dopasowujemy
c          faze i amplitude) + liczba czestosci bazowych (tylko tyle
c          wartosci czestosci trzeba dopasowywac, reszta jest liniowa
c          kombinacja czestosci bazowych)
c
      mm = 2*m + mfreq + 1
      read (3,*) a0
      write(*,*) a0
c
c   Zbior "param.sin" zawiera tez czestosci bazowe, informacje o harmonikach
c   i czestosciach kombinacyjnych!!!
c
      do i = 1,mfreq
         read (3,*) freqb(i)
         write(*,*) freqb(i)
      end do
      do i = 1,m
         read (3,*) (nharm(i,j), j = 1,mfreq)
         write(*,*) (nharm(i,j), j = 1,mfreq)
         read (3,*) amp(i),fi(i)
         write(*,*) amp(i),fi(i)
      end do
      close(3)


      do 20 i = 1,m
         freq(i) = 0.d0
         do j = 1,mfreq
            freq(i) = freq(i) + nharm(i,j)*freqb(j)
         end do
   20 continue


c ASSUMED : PHOTOMETRY,  VAR - COMPARISON !

c
c   reading data file (2nd parameter)
c
      open (1,file = 'ampl')
      n = 0
      swag = 0.d0
      open(2,file = 'lc.data')
  97  continue
      n = n + 1
      if (narg.eq.1) read (2,*,end=98) ti(n),y(n),err(n)
c      if (narg.eq.1) read (2,*,end=98) ti(n),y(n),err(n),amass(n)
      waga(n) = 1.d0/err(n)
      swag = swag + waga(n)
      go to 97
  98  n = n - 1
c
c
c
      nit = 0
   3  continue
      do i = 1,m
         per(i) = 1.d0/freq(i)
         om(i) = pi2*freq(i)
      end do
c
      sum = 0.d0
         do 10 j = 1,n
   10 sum = sum + ti(j)
      taver = sum/dble(n)

      var = 0.d0
      do i = 1,n
         sum = 0.d0
         do j = 1,m
            sum = sum + amp(j)*dsin(om(j)*ti(i) + fi(j))
         end do
         calc = a0 + sum
         res(i) = y(i) - calc
         var = var + res(i)*res(i)
      end do

      do i = 1,mm
         x(i) = 0.d0
         ia(i) = 1
      end do
      call lfit (ti,res,waga,n,x,ia,mm,mfreq,covar,chisq,nonlin)

      sdev = dsqrt(var/dble(n - 1))

      rat = dble(n)/(swag*sdev*sdev)

c      open (3, file = 'covar.mtx')
      do i = 1,mm
         do j = 1,mm
             covar(i,j) = covar(i,j)/rat
c             if (i.ge.j) write (3,'(f10.5)') covar(i,j)/covar(1,1)
        end do
c         write (3,'('' '')')
      end do
c      close(3)
      do i = 1,mm
         eps(i) = dsqrt(covar(i,i))
      end do
      write (*,'(/'' Iteration : '',i5)') nit
      nit = nit + 1
      write (*,'('' CHISQ: '',f10.5)') chisq*rat/dble(n-mm)

      ss = 0.d0
      write (*,'(12x,''     Value     Corr/Error   Error '')')
      rr = x(1)/eps(1)
      ss = ss + dabs(rr)
      write (*,'(''        a0: '',f12.4,f9.4,f11.4)') a0,
     *      rr,eps(1)
      do i = 1,mfreq
         if (eps(i+1).gt.1.d-8) then
             rr = x(i+1)/eps(i+1)
         else
             rr = 0.d0
         end if
         ss = ss + dabs(rr)
         write (*,'('' B.Fr. #'',i2,'': '',f12.7,f9.4,f11.7)')
     *        i,freqb(i),rr,eps(i+1)
      end do
      do i = 1,m
         write (*,'('' Freq. #'',i2,'': '',f12.7)') i,freq(i)
      end do
      do i = 1,m
         if (eps(mfreq+2*i).gt.1.d-8) then
             rr = x(mfreq+2*i)/eps(mfreq+2*i)
         else
             rr = 0.d0
         end if
         ss = ss + dabs(rr)
         write (*,'('' Ampl. #'',i2,'': '',f12.6,f9.4,f11.6)')
     *        i,amp(i),x(mfreq + 2*i),eps(mfreq + 2*i)
      end do
      do i = 1,m
         if (eps(mfreq+2*i+1).gt.1.d-8) then
             rr = x(mfreq+2*i+1)/eps(mfreq+2*i+1)
         else
             rr = 0.d0
         end if
         ss = ss + dabs(rr)
         write (*,'('' Phase #'',i2,'': '',f12.6,f9.4,f11.6)')
     *        i,fi(i),x(mfreq+2*i+1),eps(mfreq+2*i+1)
      end do
      write (*,'('' Sum of corr/err.: '',f10.4)') ss
      if ((ss.gt.cstop).and.(nit.lt.501)) then
         a0 = a0 + x(1)*fact
         do i = 1,mfreq
            freqb(i) = freqb(i) + x(i+1)*fact
         end do
         do i = 1,m
            freq(i) = 0.d0
            do j = 1,mfreq
               freq(i) = freq(i) + nharm(i,j)*freqb(j)
            end do
            amp(i) = amp(i) + x(mfreq+2*i)*fact
            fi(i) = fi(i) + x(mfreq+2*i+1)*fact
            if (fi(i).lt.0.d0) fi(i) = fi(i) + pi2
            fi(i) = dmod(fi(i),pi2)
         end do
         goto 3
      else
         open (3, file = 'hars-ite.err')
         if (nit.lt.501) then
            write (3,'(''0'')')
         else
            write (3,'(''1'')')
         end if
         close(3)
      end if

      open (3,file = 'resid.dat')
      var = 0.d0
      do 7 i = 1,n
          sum = 0.d0
          do j = 1,m
             sum = sum + amp(j)*dsin(om(j)*ti(i) + fi(j))
          end do
          calc = a0 + sum
          oc = y(i) - calc
          var = var + oc*oc
        if (narg.eq.1) write (3,'(2f16.7,f10.5)') ti(i),oc,err(i)
c        if (narg.eq.1) write (3,'(2f13.7,2f10.5)') ti(i),oc,err(i),
c     *      amass(i)
    7 continue
      sdev = dsqrt(var/dble(n - 1))
      write (*,'('' Nobs:  '',i8)') n
      write (*,'('' SDEV:  '',f12.5)') sdev
      write (1,'('' Nobs:  '',i8)') n
      write (1,'('' SDEV:  '',f12.5)') sdev
      close(3)

      do ii = 1,mfreq
c         open (3, file = '$$$.res')
         if (ii.lt.10) then
            write (c,'(''0'',i1)') ii
         else
            write (c,'(i2)') ii
         end if
c         close(3)
c         open (3, file = '$$$.res')
c         read (3,'(a2)') c
c         close(3)
         nameb = 'resid' // c // '.dat'
         open (3, file = nameb)
         do j = 1,m
            idx(j) = 1
         end do
         do j = 1,m
           nsum = 0
           do k = 1,mfreq
              nsum = nsum + abs(nharm(j,k))
           end do
           if ((nharm(j,ii).ne.0).and.(nsum.eq.abs(nharm(j,ii))))
     *         idx(j) = 0
         end do
         do i = 1,n
          sum = 0.d0
          do j = 1,m
             sum = sum + idx(j)*amp(j)*dsin(om(j)*ti(i) + fi(j))
          end do
          calc = a0 + sum
          oc = y(i) - calc
          write (3,'(2f13.4,f12.4)') ti(i),oc,1.d0/dsqrt(waga(i))
         end do
         close(3)
      end do


      write (1,'('' Data file : lc.data'')')
      write (1,'(''            a0: '',f12.4,f11.4)') a0,eps(1)
      do i = 1,mfreq
         write (1,'('' Basic fr. #'',i3,'': '',2f12.7)')
     *        i,freqb(i),eps(i+1)
      end do
      do i = 1,m
         write (1,'('' Frequency #'',i3,'': '',f13.7)') i,freq(i)
      end do
      do i = 1,m
         write (1,'('' Ampl. #'',i3,'': '',2f11.6)')
     *        i,amp(i),eps(mfreq + 2*i)
      end do
      do i = 1,m
         write (1,'('' Phase #'',i3,'': '',2f11.6)')
     *        i,fi(i),eps(mfreq+2*i+1)
      end do
      do i = 1,m
         tmax(i) = (-.25d0 - fi(i)/pi2)*per(i)
         ncyc = idint ((taver - tmax(i) + 0.5d0*per(i))/per(i))
         tmax(i) = tmax(i) + dble(ncyc)*per(i)
         write (1,'(''  Tmax #'',i3,'': '',f15.8,f11.8)')
     *        i,tmax(i),eps(mfreq+2*i+1)*per(i)/pi2
      end do
      stop
      end


      subroutine lfit(x,y,wei,ndat,a,ia,ma,mfreq,covar,
     *                chisq,funcs)
c
c   ndat - number of points,
c   x(1...ndat) - abscissae of points,
c   y(1...ndat) - ordinates of points,
c   wei(1...ndat) - weights of points,
c   ma - number of parameters to derive,
c   a(1...ma) - table of parameters,
c   ia(1...ma) - table of 0,1, 1 means that a given parameter is fitted,
c   covar(1...ma,1...ma) - covariance matrix,
c   chisq - Chi squared,
c   funcs(x,afunc,ma,mfreq) - a routine supplied by the user.
c
c   Given a set of data points x(1...ndat), y(1,ndat) with individual
c   weights wei(1...ndat), use Chi^2 minimization to fit for some or all
c   of the coefficients a(1...ma) of a function that depends linearly on a,
c   y = sum of a_i * func_i(x).  The input array ia(1...ma) indicates by
c   nonzero entries those components of a that should be fitted for, and by
c   zero entries those components that should be held fixed at their input
c   values.  The program returns values for a(1...ma), chi^2 = chisq, and
c   the covariance matrix covar(1...ma,1...ma).  (Parameters held fixed
c   will return zero covariances.)  The user supplies a routine
c   funcs(x,afunc,ma) that returns the ma basis functions evaluated at
c   x = X in the array afunc(1...ma).
c
      implicit double precision (a-h,o-z)
      external nonlin
      parameter (NP = 1000000,NPAR = 1500, NHAR = 500, NPER = 500)
      dimension x(NP),y(NP),wei(NP),sig(NP),
     *          a(NPAR),ia(NPAR),beta(NPAR),afunc(NPAR),
     *          covar(NPAR,NPAR),freq(NPER),fi(NPER),amp(NPER),
     *          freqb(NPER),nharm(NHAR,NPER)
      common /fff/ freq,fi,amp,freqb,nharm
c
c  Change sigmas to weights
c
      do i = 1,ndat
         sig(i) = 1.d0/dsqrt(wei(i))
      end do
c
c  Evaluate number of parameters to be fitted
c
      mfit = 0
      do j = 1,ma
         if (ia(j).eq.1) mfit = mfit + 1
      end do
      if (mfit.eq.0) then
         write (*,'('' LFIT: no parameters to be fitted!'')')
         stop
      end if
      if (mfit.ne.ma) write (*,'('' mfit less than ma ! '')')
c
c  Initialize the (symmetric) matrix.
c
      do j = 1,mfit
         do k = 1,mfit
            covar(j,k) = 0.d0
         end do
         beta(j) = 0.d0
      end do
c
c  Loop over data to accumulate coefficients of the normal equations.
c
       do i = 1,ndat
          call funcs(x(i),afunc,ma,mfreq)
          ym = y(i)
c
c  Subtract off dependencies on known pieces of the fitting function
c
          if (mfit.lt.ma) then
             do j = 1,ma
                if (ia(j).eq.0) ym = ym - a(j)*afunc(j)
             end do
          end if
          sig2i = wei(i)

          j = 0
          do l = 1,ma
             if (ia(l).eq.1) then
                wt = afunc(l)*sig2i
                k = 0
                j = j + 1
                do m = 1,l
                   if(ia(m).eq.1) then
                      k = k + 1
                      covar(j,k) = covar(j,k) + wt*afunc(m)
                   end if
                end do
                beta(j) = beta(j) + ym*wt
             end if
          end do
       end do
c
c   Fill in above the diagonal from symmetry
c
      do j = 2,mfit
         do k = 1,j-1
            covar(k,j) = covar(j,k)
         end do
      end do
c
c   Matrix solution.
c
      call gaussj(covar,mfit,beta,1)
c
c   Partition solution to appropriate coefficients
c
      j = 0
      do l = 1,ma
         if (ia(l).eq.1) then
            j = j + 1
            a(l) = beta(j)
         end if
      end do
c
c   Evaluate Chi^2
c
      chisq = 0.d0
      do i = 1,ndat
         call funcs(x(i),afunc,ma,mfreq)
         sum = 0.d0
         do j = 1,ma
            sum = sum + a(j)*afunc(j)
         end do
         chisq = chisq + ((y(i) - sum)/sig(i))**2
      end do
c
c   Sort covariance matrix to true order of fitting coefficients.
c
      call covsrt(covar,ma,ia,mfit)
      return
      end

      subroutine gaussj(a,n,b,m)
c
c   Linear equation solution by Gauss-Jordan elimination.  Input matrix:
c   a(1...n,1...n),  b(1...n,1...m) is input containing the m right-hand
c   side vectors.  On input, a is replaced by its matrix inverse, and b
c   is replaced by the corresponding set of solution vectors.
c
      implicit double precision (a-h,o-z)
      parameter (NP = 1000000,NPAR = 1500)
      dimension indxc(NPAR),indxr(NPAR),ipiv(NPAR)
      dimension a(NPAR,NPAR),b(NPAR,NPAR)
      irow = 0
      icol = 0
      do j = 1,n
         ipiv(j) = 0
      end do
      do i = 1,n
         big = 0.d0
         do j = 1,n
            if (ipiv(j).ne.1) then
               do k = 1,n
                  if (ipiv(k).eq.0) then
                     if (dabs(a(j,k)).ge.big) then
                        big = dabs(a(j,k))
                        irow = j
                        icol = k
                     end if
                  else
                     if (ipiv(k).gt.1) write (*,'('' Sing. Matrix'')')
                  end if
               end do
            end if
         end do
         ipiv(icol) = ipiv(icol) + 1
         if (irow.ne.icol) then
            do l = 1,n
               call SWAP(a(irow,l),b(icol,l))
            end do
            do l = 1,m
               call SWAP(b(irow,l),b(icol,l))
            end do
         end if
         indxr(i) = irow
         indxc(i) = icol
         if (a(icol,icol).eq.0.d0) then
            write (*,'('' Singular matrix 2'')')
            stop
         end if
         pivinv = 1.d0/a(icol,icol)
         a(icol,icol) = 1.d0
         do l = 1,n
            a(icol,l) = a(icol,l)*pivinv
         end do
         do l = 1,m
            b(icol,l) = b(icol,l)*pivinv
         end do
         do ll = 1,n
            if (ll.ne.icol) then
               dum = a(ll,icol)
               a(ll,icol) = 0.d0
               do l = 1,n
                 a(ll,l) = a(ll,l) - a(icol,l)*dum
               end do
               do l = 1,m
                 b(ll,l) = b(ll,l) - b(icol,l)*dum
               end do
            end if
         end do
      end do

      do l = n,1,-1
         if (indxr(l).ne.indxc(l)) then
            do k = 1,n
               call SWAP(a(k,indxr(l)),a(k,indxc(l)))
            end do
         end if
      end do
      return
      end


      subroutine covsrt(covar,ma,ia,mfit)
      implicit double precision (a-h,o-z)
      parameter (NP = 1000000,NPAR = 1500)
      dimension covar(NPAR,NPAR),ia(NPAR)
      do i = mfit+1,ma
         do j = 1,i
            covar(i,j) = 0.d0
            covar(j,i) = 0.d0
         end do
      end do
      k = mfit
      do j = ma,1,-1
         if (ia(j).eq.1) then
            do i = 1,ma
               call SWAP(covar(i,k),covar(i,j))
            end do
            do i = 1,ma
               call SWAP(covar(k,i),covar(j,i))
            end do
            k = k - 1
         end if
      end do
      return
      end

      subroutine SWAP(a,b)
      double precision a,b,sw
      sw = a
      a = b
      b = sw
      return
      end

      subroutine nonlin(x,afunc,ma,mfreq)
      implicit double precision (a-h,o-z)
      parameter (NP = 1000000,NPAR = 1500, NHAR = 500, NPER = 500)
      dimension afunc(NPAR),freq(NPER),fi(NPER),amp(NPER),
     *          freqb(NPER),nharm(NHAR,NPER)
      common /fff/ freq,fi,amp,freqb,nharm
      data pi2 /6.2831853072d0/
      afunc(1) = 1.d0
      nfr = (ma - mfreq - 1)/2
      do i = 1,mfreq
        afunc(i+1) = 0.d0
        do j = 1,nfr
           omt = freq(j)*pi2*x + fi(j)
           afunc(i+1) = afunc(i+1) + pi2*x*amp(j)*dcos(omt)*
     *                  dble(nharm(j,i))
c          write(*,'(3i5,f20.5)') i,j,nharm(j,i),afunc(i+1)
        end do
      end do
      do i = 1,nfr
         omt = freq(i)*pi2*x + fi(i)
         afunc(mfreq + 2*i) = dsin(omt)
         afunc(mfreq + 1 + 2*i) = amp(i)*dcos(omt)
      end do
      return
      end


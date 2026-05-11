c
c  dopasowuje n sinusoid (+ harmoniki + czestosci kombinacyjne)
c  do danych obserwacyjnych postaci: czas,mag,blad
c
      program sinn
      implicit double precision (a-h,o-z)
      external linsin
      parameter (NP = 1000000,NPAR = 1000,NPER = 500)
      dimension y(NP),ti(NP),x(NPAR),eps(NPAR),per(NPER),
     *     a(NPER),dela(NPER),fi(NPER),delfi(NPER),TMAX(NPER),
     *     freq(NPER),om(NPER),waga(NP),covar(NPAR,NPAR),ia(NPAR),
     *     freqb(NPER),nharm(NPER,5*NPER),err(NP)
      data pi2 /6.2831853072d0/

      write (*,'(/'' --- hars-sin, ver. 2.0, 22 Oct 2014 ---'')')
      write (*,'('' Defaults names:'')')
      write (*,'(''  I - data file: lc.data'')')
      write (*,'(''  I - freq: frequency file'')')
      write (*,'(''  O - param.sin: input file for hars-ite'')')
      write (*,'(''  O - ampl: parameter file'')')
c
c   file "freq" contains frequencies!!!
c
      open (1,file='freq')
      read (1,*) mfreq,m
c
c  mfreq - number of basic frequencies
c  m - number of sinusoidal terms
c  mm - number of unknowns
c
      mm = 2*m + 1
      do 21 i = 1,mfreq
         read (1,*) freqb(i)
   21 continue
      do 20 i = 1,m
         read (1,*) (nharm(j,i), j = 1,mfreq)
         freq(i) = 0.d0
         do j = 1,mfreq
            freq(i) = freq(i) + nharm(j,i)*freqb(j)
         end do
   20 continue
      close(1)

c ASSUMED : PHOTOMETRY,  VAR - COMPARISON !

c
c   reading data file (2nd parameter)
c
c   Zbior danych powinien zawierac:
c    kol. 1:  czas
c    kol. 2:  jasnosc (zmienna - porown.)
c    kol. 3:  blad (<> 0 !!!)
c  opcjonalnie:
c    kol. 4:  masa powietrzna
c
      open (1,file = 'ampl')
      n = 0
      swag = 0.d0
      open (2,file = 'lc.data')
  97  continue
      n = n + 1

c     

      read (2,*,end=98) ti(n),y(n),err(n)
      waga(n) = 1.d0/err(n)
      swag = swag + waga(n)
      go to 97
  98  n = n - 1
c
c
c
      do i = 1,m
         per(i) = 1.d0/freq(i)
         om(i) = pi2/per(i)
      end do
c
c
      sum = 0.d0
         do 10 j = 1,n
   10 sum = sum + ti(j)
      taver = sum/dble(n)
      do i = 1,mm
          ia(i) = 1
      end do

      do i = 1,mm
         x(i) = 0.d0
      end do
      call lfit (ti,y,waga,n,x,ia,mm,covar,chisq,linsin,freq)

      do 15 i = 1,m
         k = 2*i
         l = k + 1
         fi(i) = datan(x(l)/x(k))
         if ((x(k).gt.0).and.(x(l).lt.0)) then
            fi(i) = fi(i) + pi2
         else
            if (x(k).lt.0) fi(i) = fi(i) + pi2/2.d0
         end if
         a(i) = dsqrt(x(k)*x(k) + x(l)*x(l))
   15 continue


c      open (3,file = 'oc.dat')
      var = 0.d0
      DO 7 I = 1,N
          sum = 0.d0
          do j = 1,m
             sum = sum + a(j)*dsin(om(j)*ti(i) + fi(j))
          end do
          calc = x(1) + sum
          oc = y(i) - calc
          var = var + oc*oc
c        write (3,'(3f12.5,f10.5)') ti(i),oc,calc,err(i)
    7 continue
c      close(3)
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

      do i = 1,m
         k = 2*i
         l = k + 1
         DELfi(i) = dsqrt(eps(l)**2 + (dabs(x(l)*eps(k)/x(k)))**2)/
     *            (dabs(x(k))*(1.d0 + (dabs(x(l)/x(k)))**2))
         DELa(i) = dsqrt((X(k)*EPS(k))**2 + (X(l)*EPS(l))**2) / a(i)
      end do
      DELA0 = EPS(1)


C     DATA OUTPUT

c     write (1,'('' Data file : '',a12)')
      write (*,'('' '')')
      write (*,'('' '')')
      write (1,'('' '')')
      WRITE (*,'(''       FREQ.      PERIOD        N         A0      '',
     *           ''   AMPL.     PHASE          TMAX     '',
     *           ''  SDEV'')')
      WRITE (1,'(''       FREQ.      PERIOD        N         A0      '',
     *           ''   AMPL.     PHASE          TMAX     '',
     *           ''  SDEV'')')
      write (1,'('' '')')
      write (*,'('' '')')

      do i = 1,m
         tmax(I) = (-.25d0 - fi(i)/pi2)*per(i)
         ncyc = dint ((taver - tmax(i) + 0.5d0*per(i))/per(i))
         tmax(i) = tmax(i) + dble(ncyc)*per(i)
      if (i.eq.1) then
         write (1,'(F13.7,F14.10,I6,2F13.5,F9.4,F18.8,F10.5)')
     *        freq(i),per(i),n,x(1),a(i),fi(i),TMAX(I),SDEV
         write (*,'(F13.7,F14.10,I6,2F13.5,F9.4,F18.8,F10.5)')
     *        freq(i),per(i),n,x(1),a(i),fi(i),TMAX(i),SDEV
         write (1,'(F46.5,F13.5,F9.4,F18.8)')
     *        DELA0,DELA(i),DELFI(i),DELFI(I)*PER(i)/PI2
         write (*,'(F46.5,F13.5,F9.4,F18.8)')
     *        DELA0,DELA(i),DELFI(i),DELFI(i)*PER(i)/PI2
         WRITE (*,'('' '')')

      else
         write (1,'(F13.7,F14.10,19x,F13.5,F9.4,F18.8)')
     *        freq(i),per(i),a(i),fi(i),TMAX(I)
         write (*,'(F13.7,F14.10,19x,F13.5,F9.4,F18.8)')
     *        freq(i),per(i),a(i),fi(i),TMAX(i)
         write (1,'(F59.5,F9.4,F18.8)')
     *        DELA(i),DELFI(i),DELFI(I)*PER(i)/PI2
         write (*,'(F59.5,F9.4,F18.8)')
     *        DELA(i),DELFI(i),DELFI(i)*PER(i)/PI2
         WRITE (*,'('' '')')
      end if
      end do

      open (3,file = 'param.sin')
      write (3,'(2i5)') mfreq, m
      write (3,'(F14.4)') x(1)
      do i = 1,mfreq
         write (3,'(f13.7)') freqb(i)
      end do
      do i = 1,m
        
            write (3,*) (nharm(j,i), j = 1,mfreq)
        
         write (3,'(F15.8,F12.6)') a(i),fi(i)
      end do
      close(3)
      write (*,'('' CHISQ: '',f10.5)') chisq*rat/dble(n-mm)
      stop
      end


      subroutine lfit(x,y,wei,ndat,a,ia,ma,covar,chisq,funcs,freq)
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
c   funcs(x,afunc,ma,freq) - a routine supplied by the user.
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
      external funcs
      parameter (NP = 1000000,NPAR = 1000)
      dimension x(NP),y(NP),wei(NP),sig(NP),
     *          a(NPAR),ia(NPAR),beta(NPAR),afunc(NPAR),
     *          covar(NPAR,NPAR),freq(NPAR)
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
          call funcs(x(i),afunc,ma,freq)
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
         call funcs(x(i),afunc,ma,freq)
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
      parameter (NP = 1000000,NPAR = 1000)
      dimension indxc(NPAR),indxr(NPAR),ipiv(NPAR)
      dimension a(NPAR,NPAR),b(NPAR,NPAR)
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
      parameter (NP = 1000000,NPAR = 1000)
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

      subroutine linsin(x,afunc,ma,freq)
      implicit double precision (a-h,o-z)
      parameter (NPAR = 1000,NFREQ = 500)
      dimension afunc(NPAR),freq(NFREQ)
      data pi2 /6.2831853072d0/
      afunc(1) = 1.d0
      nfr = (ma - 1)/2
      do i = 1,nfr
         afunc(2*i) = dsin(pi2*freq(i)*x)
         afunc(2*i+1) = dcos(pi2*freq(i)*x)
      end do
      return
      end

